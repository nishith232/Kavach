package app.kavach.guard.core

import android.content.Context
import android.content.SharedPreferences
import java.io.File
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

data class RedFlag(val quote: String, val why: String)

data class Alert(
    val id: String,
    val time: Long,
    val appName: String,
    val pkg: String,
    val original: String,
    val verdict: String,
    val risk: Int,
    val scamType: String,
    val scamTypeLocal: String,
    val summary: String,
    val redFlags: List<RedFlag>,
    val facts: List<String>,
    val actions: List<String>,
    val language: String,
    val source: String,          // "ai" (server verdict) or "on-device" (keyword rules only)
    val localLabels: List<String>,
    val audioPath: String?,
    val spoken: String = "",
    val languageCode: String = "",
    val sender: String = "",
    // "checking" (AI pending) | "clean" (on-device: no warning signs, not sent to AI) | "done" (AI verdict)
    // | "offline" (on-device warning, AI unreachable) | "error" (AI unreachable, not judged)
    val status: String = "done",
) {
    val isThreat: Boolean get() = verdict in setOf("SCAM", "LIKELY_SCAM", "SUSPICIOUS")
    val isFraud: Boolean get() = verdict in setOf("SCAM", "LIKELY_SCAM")
    val isGenuine: Boolean get() = verdict in setOf("LIKELY_SAFE", "CLEAN")
    val aiChecked: Boolean get() = source == "ai"

    /** Compact form sent to the voice assistant (it only reasons over these real records). */
    fun toAssistantJson(): JSONObject = JSONObject().apply {
        put("id", id); put("time", time); put("app", appName); put("sender", sender); put("verdict", verdict)
        put("risk", risk); put("scam_type", scamType); put("summary", summary.take(400))
        put("snippet", original.replace('\n', ' ').take(160))
        put("red_flags", JSONArray(redFlags.map { it.quote }.filter { it.isNotBlank() }.take(3)))
        put("actions", JSONArray(actions.take(2)))
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id); put("time", time); put("appName", appName); put("pkg", pkg); put("original", original)
        put("verdict", verdict); put("risk", risk); put("scamType", scamType); put("scamTypeLocal", scamTypeLocal)
        put("summary", summary); put("language", language); put("source", source); put("audioPath", audioPath ?: ""); put("spoken", spoken); put("languageCode", languageCode)
        put("sender", sender); put("status", status)
        put("redFlags", JSONArray(redFlags.map { JSONObject().put("quote", it.quote).put("why", it.why) }))
        put("facts", JSONArray(facts)); put("actions", JSONArray(actions)); put("localLabels", JSONArray(localLabels))
    }

    companion object {
        fun fromJson(o: JSONObject): Alert = Alert(
            id = o.optString("id"), time = o.optLong("time"), appName = o.optString("appName"), pkg = o.optString("pkg"),
            original = o.optString("original"), verdict = o.optString("verdict"), risk = o.optInt("risk"),
            scamType = o.optString("scamType"), scamTypeLocal = o.optString("scamTypeLocal"), summary = o.optString("summary"),
            redFlags = o.optJSONArray("redFlags").objects().map { RedFlag(it.optString("quote"), it.optString("why")) },
            facts = o.optJSONArray("facts").strings(), actions = o.optJSONArray("actions").strings(),
            language = o.optString("language"), source = o.optString("source"),
            localLabels = o.optJSONArray("localLabels").strings(),
            audioPath = o.optString("audioPath").ifBlank { null },
            spoken = o.optString("spoken"),
            languageCode = o.optString("languageCode"),
            sender = o.optString("sender"),
            status = o.optString("status", "done"),
        )
    }
}

fun JSONArray?.strings(): List<String> =
    if (this == null) emptyList() else (0 until length()).map { optString(it) }.filter { it.isNotBlank() }

fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

data class Settings(
    val serverUrl: String = "http://192.168.1.10:8000",
    val replyLanguage: String = "auto",
    val speakAlerts: Boolean = true,
    val scanAllApps: Boolean = true,
    val alertOnSuspicious: Boolean = true,
    val aiEveryMessage: Boolean = false,
)

data class Stats(val day: String = "", val scannedToday: Int = 0, val flaggedTotal: Int = 0, val aiChecks: Int = 0)

/**
 * App-wide state shared by the notification service and the UI. Persisted in SharedPreferences.
 * `alerts` holds EVERY scanned message as a record (newest first), not only threats, so the user can
 * open any message Kavach checked. The key is unchanged, so alerts saved by older versions still load.
 */
object Store {
    private lateinit var prefs: SharedPreferences
    private const val MAX_RECORDS = 200

    private val _alerts = MutableStateFlow<List<Alert>>(emptyList())
    val alerts: StateFlow<List<Alert>> = _alerts.asStateFlow()

    private val _settings = MutableStateFlow(Settings())
    val settings: StateFlow<Settings> = _settings.asStateFlow()

    private val _stats = MutableStateFlow(Stats())
    val stats: StateFlow<Stats> = _stats.asStateFlow()

    private val _listenerConnected = MutableStateFlow(false)
    val listenerConnected: StateFlow<Boolean> = _listenerConnected.asStateFlow()

    private val recent = LinkedHashMap<Int, Long>()  // text hash -> time, to skip duplicate notifications

    fun init(ctx: Context) {
        prefs = ctx.getSharedPreferences("kavach", Context.MODE_PRIVATE)
        _settings.value = Settings(
            serverUrl = prefs.getString("serverUrl", Settings().serverUrl)!!,
            replyLanguage = prefs.getString("replyLanguage", "auto")!!,
            speakAlerts = prefs.getBoolean("speakAlerts", true),
            scanAllApps = prefs.getBoolean("scanAllApps", true),
            alertOnSuspicious = prefs.getBoolean("alertOnSuspicious", true),
            aiEveryMessage = prefs.getBoolean("aiEveryMessage", false),
        )
        _alerts.value = runCatching {
            JSONArray(prefs.getString("alerts", "[]")).objects().map { Alert.fromJson(it) }
        }.getOrDefault(emptyList())
        _stats.value = Stats(
            day = prefs.getString("statsDay", "")!!,
            scannedToday = prefs.getInt("scannedToday", 0),
            flaggedTotal = prefs.getInt("flaggedTotal", 0),
            aiChecks = prefs.getInt("aiChecks", 0),
        )
    }

    fun updateSettings(transform: (Settings) -> Settings) {
        _settings.update(transform)
        val s = _settings.value
        prefs.edit()
            .putString("serverUrl", s.serverUrl.trim().trimEnd('/'))
            .putString("replyLanguage", s.replyLanguage)
            .putBoolean("speakAlerts", s.speakAlerts)
            .putBoolean("scanAllApps", s.scanAllApps)
            .putBoolean("alertOnSuspicious", s.alertOnSuspicious)
            .putBoolean("aiEveryMessage", s.aiEveryMessage)
            .apply()
    }

    fun setListenerConnected(v: Boolean) { _listenerConnected.value = v }

    /** Insert or update a record (same id = same message), keeping its place in time order. */
    @Synchronized
    fun addAlert(alert: Alert) {
        val previous = _alerts.value.firstOrNull { it.id == alert.id }
        val record = alert.copy(original = alert.original.take(4000))
        val all = (_alerts.value.filterNot { it.id == alert.id } + record).sortedByDescending { it.time }
        val kept = all.take(MAX_RECORDS)
        all.drop(MAX_RECORDS).forEach { deleteAudio(it) }
        _alerts.value = kept
        persist()
        if (record.isThreat && previous?.isThreat != true) bumpStats { it.copy(flaggedTotal = it.flaggedTotal + 1) }
    }

    private fun persist() {
        prefs.edit().putString("alerts", JSONArray(_alerts.value.map { it.toJson() }).toString()).apply()
    }

    private fun deleteAudio(a: Alert) {
        a.audioPath?.let { runCatching { File(it).delete() } }
    }

    /** The most recent records for the voice assistant, as JSON. */
    fun assistantRecords(limit: Int = 150): String =
        JSONArray(_alerts.value.filter { it.status != "checking" }.take(limit).map { it.toAssistantJson() }).toString()

    fun alert(id: String?): Alert? = _alerts.value.firstOrNull { it.id == id }

    @Synchronized
    fun clearAlerts() {
        _alerts.value.forEach { deleteAudio(it) }
        _alerts.value = emptyList()
        prefs.edit().putString("alerts", "[]").apply()
    }

    fun countScanned() = bumpStats { it.copy(scannedToday = it.scannedToday + 1) }
    fun countAiCheck() = bumpStats { it.copy(aiChecks = it.aiChecks + 1) }

    @Synchronized
    private fun bumpStats(change: (Stats) -> Stats) {
        val today = LocalDate.now().toString()
        val base = _stats.value.let { if (it.day != today) it.copy(day = today, scannedToday = 0) else it }
        val s = change(base)
        _stats.value = s
        prefs.edit().putString("statsDay", s.day).putInt("scannedToday", s.scannedToday)
            .putInt("flaggedTotal", s.flaggedTotal).putInt("aiChecks", s.aiChecks).apply()
    }

    /** True if this exact text was already handled in the last 10 minutes (apps re-post notifications). */
    @Synchronized
    fun isDuplicate(text: String): Boolean {
        val now = System.currentTimeMillis()
        recent.entries.removeAll { now - it.value > 10 * 60_000 }
        val key = text.trim().hashCode()
        if (recent.containsKey(key)) return true
        recent[key] = now
        return false
    }

    fun cachedRules(): String? = prefs.getString("rulesJson", null)
    fun cacheRules(json: String) = prefs.edit().putString("rulesJson", json).apply()
}
