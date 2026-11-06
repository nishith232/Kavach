package app.kavach.guard.core

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * message text -> on-device keyword scan -> (if suspicious) AI verdict from the server
 * -> saved alert -> heads-up notification + optional spoken warning in the user's language.
 */
object Pipeline {
    enum class Mode {
        AUTO,    // from the notification listener: only suspicious text goes to the server
        MANUAL,  // user pasted text in the app: always analysed, no notification
        DEMO,    // "simulate" button: always analysed and always notifies
    }

    /** Minimum on-device signal before a notification is sent to the AI. */
    private fun worthChecking(scan: RuleEngine.Scan) = scan.score >= 3 || scan.floor >= 35

    suspend fun process(ctx: Context, text: String, pkg: String, appName: String, mode: Mode): Alert? {
        val scan = RuleEngine.scan(text)
        if (mode == Mode.AUTO && !worthChecking(scan)) return null

        val settings = Store.settings.value
        val wantVoice = settings.speakAlerts && mode != Mode.MANUAL
        val alert = try {
            val json = Api.analyze(settings.serverUrl, text, if (wantVoice) "both" else "text", settings.replyLanguage)
            Store.countAiCheck()
            fromServer(ctx, json, text, pkg, appName, scan)
        } catch (e: Exception) {
            when {
                mode == Mode.MANUAL -> throw e
                scan.floor >= 60 -> offline(text, pkg, appName, scan)   // strong on-device signal: still warn
                mode == Mode.DEMO -> offline(text, pkg, appName, scan)
                else -> return null
            }
        }

        Store.addAlert(alert)
        val notify = mode != Mode.MANUAL &&
            (alert.verdict in setOf("SCAM", "LIKELY_SCAM") || (alert.verdict == "SUSPICIOUS" && settings.alertOnSuspicious))
        if (notify) {
            Notifier.showAlert(ctx, alert)
            if (wantVoice) Notifier.speak(alert.audioPath)
        }
        return alert
    }

    private fun fromServer(
        ctx: Context, json: JSONObject, text: String, pkg: String, appName: String, scan: RuleEngine.Scan,
    ): Alert {
        val r = json.getJSONObject("result")
        val id = UUID.randomUUID().toString()
        val audioPath = json.optString("audio_b64").takeIf { it.isNotBlank() && it != "null" }?.let { b64 ->
            runCatching {
                val f = File(ctx.filesDir, "voice_$id.wav")
                f.writeBytes(Base64.decode(b64, Base64.DEFAULT))
                f.absolutePath
            }.getOrNull()
        }
        return Alert(
            id = id,
            time = System.currentTimeMillis(),
            appName = appName,
            pkg = pkg,
            original = text,
            verdict = r.optString("verdict", "NOT_ENOUGH_INFO"),
            risk = r.optInt("risk_score", scan.floor),
            scamType = r.optString("scam_type"),
            scamTypeLocal = r.optString("scam_type_local"),
            summary = r.optString("summary"),
            redFlags = r.optJSONArray("red_flags").objects().map { RedFlag(it.optString("quote"), it.optString("why")) },
            facts = r.optJSONArray("facts").strings(),
            actions = r.optJSONArray("actions").strings(),
            language = r.optString("language_name", r.optString("language")),
            source = "ai",
            localLabels = scan.labels,
            audioPath = audioPath,
        )
    }

    private fun offline(text: String, pkg: String, appName: String, scan: RuleEngine.Scan): Alert {
        val verdict = when {
            scan.floor >= 80 -> "LIKELY_SCAM"
            scan.floor >= 35 -> "SUSPICIOUS"
            else -> "NOT_ENOUGH_INFO"
        }
        return Alert(
            id = UUID.randomUUID().toString(),
            time = System.currentTimeMillis(),
            appName = appName,
            pkg = pkg,
            original = text,
            verdict = verdict,
            risk = scan.floor,
            scamType = "",
            scamTypeLocal = "",
            summary = "Kavach couldn't reach its AI server, but this message matches known scam patterns: " +
                scan.labels.take(3).joinToString("; ") + ". Don't share OTPs, PINs or money, and don't call numbers in the message.",
            redFlags = scan.hits.map { RedFlag(it.match, it.label) },
            facts = emptyList(),
            actions = listOf("Don't reply, click links, or call numbers from this message.", "Report fraud on 1930 or cybercrime.gov.in."),
            language = "English",
            source = "on-device",
            localLabels = scan.labels,
            audioPath = null,
        )
    }

    const val DEMO_TEXT =
        "Dear Consumer, your electricity power will be disconnected tonight at 9.30 PM because your previous " +
            "month bill was not updated. Please immediately contact our electricity officer 98XXXXX310."
}
