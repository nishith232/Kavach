package app.kavach.guard.core

import android.content.Context
import android.util.Base64
import app.kavach.guard.service.ShieldListener
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

    /** Any real warning sign (one weight-2 rule) sends the message to the AI; or every chat message if enabled. */
    private fun worthChecking(scan: RuleEngine.Scan, pkg: String, settings: Settings) =
        scan.score >= 2 || scan.floor >= 35 || (settings.aiEveryMessage && ShieldListener.isMessagingApp(pkg))

    suspend fun process(ctx: Context, text: String, pkg: String, appName: String, mode: Mode): Alert? {
        val scan = RuleEngine.scan(text)
        val settings = Store.settings.value
        val eventId = UUID.randomUUID().toString()
        val logged = mode != Mode.MANUAL
        val snippet = text.substringAfter('\n', text).replace('\n', ' ').take(140)
        if (logged) {
            Store.logScan(ScanEvent(eventId, System.currentTimeMillis(), appName, snippet, "checking"))
        }
        if (mode == Mode.AUTO && !worthChecking(scan, pkg, settings)) {
            Store.updateScan(eventId) { it.copy(status = "clean") }
            return null
        }

        val wantVoice = settings.speakAlerts && mode != Mode.MANUAL
        // DEMO gets voice in the same call; AUTO asks for text only and fetches voice later, only for threats.
        val output = if (wantVoice && mode == Mode.DEMO) "both" else "text"
        var alert = try {
            val json = Api.analyze(settings.serverUrl, text, output, settings.replyLanguage)
            Store.countAiCheck()
            fromServer(ctx, json, text, pkg, appName, scan)
        } catch (e: Exception) {
            when {
                mode == Mode.MANUAL -> throw e
                scan.floor >= 60 || mode == Mode.DEMO -> offline(text, pkg, appName, scan)   // strong on-device signal: still warn
                else -> {
                    Store.updateScan(eventId) { it.copy(status = "error") }
                    return null
                }
            }
        }

        if (logged) Store.updateScan(eventId) {
            it.copy(
                status = if (alert.source == "ai") "done" else "offline",
                verdict = alert.verdict, risk = alert.risk, alertId = alert.id,
            )
        }
        // Background messages the AI calls safe stay in the live feed only; threats become alerts.
        if (mode == Mode.AUTO && !alert.isThreat) return alert
        Store.addAlert(alert)
        val notify = mode != Mode.MANUAL &&
            (alert.verdict in setOf("SCAM", "LIKELY_SCAM") || (alert.verdict == "SUSPICIOUS" && settings.alertOnSuspicious))
        if (notify) {
            Notifier.showAlert(ctx, alert)
            if (wantVoice) {
                if (alert.audioPath == null && alert.spoken.isNotBlank()) {
                    runCatching {
                        val wav = Api.speak(settings.serverUrl, alert.spoken, alert.languageCode)
                        val f = File(ctx.filesDir, "voice_${alert.id}.wav").apply { writeBytes(wav) }
                        alert = alert.copy(audioPath = f.absolutePath)
                        Store.addAlert(alert)   // same id: replaces the entry, now with audio
                    }
                }
                Notifier.speak(alert.audioPath)
            }
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
            spoken = r.optString("spoken"),
            languageCode = r.optString("language"),
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
