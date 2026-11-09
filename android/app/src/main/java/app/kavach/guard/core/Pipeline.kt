package app.kavach.guard.core

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Base64
import app.kavach.guard.service.ShieldListener
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.UUID

/**
 * message text -> on-device keyword scan -> (if suspicious) AI verdict from the server
 * -> saved record -> heads-up notification + optional spoken warning in the user's language.
 *
 * Every message the shield sees is saved as a record with a stable id (clean ones too), so the
 * user can open exactly what was scanned from Live Scan, History, a notification or the voice assistant.
 */
object Pipeline {
    enum class Mode {
        AUTO,    // from the notification listener: only suspicious text goes to the server
        MANUAL,  // user pasted text, or re-checks a record: always analysed, no notification
        DEMO,    // "simulate" button: always analysed and always notifies
    }

    /** Any real warning sign (one weight-2 rule) sends the message to the AI; or every chat message if enabled. */
    private fun worthChecking(scan: RuleEngine.Scan, pkg: String, settings: Settings) =
        scan.score >= 2 || scan.floor >= 35 || (settings.aiEveryMessage && ShieldListener.isMessagingApp(pkg))

    suspend fun process(
        ctx: Context, body: String, pkg: String, appName: String, mode: Mode,
        sender: String = "", recordId: String? = null, recordTime: Long? = null,
    ): Alert? {
        // The AI sees the sender too ("From: VM-SBIBNK" vs a 10-digit number is a useful signal).
        val text = if (sender.isNotBlank() && sender !in body) "From: $sender\n$body" else body
        val scan = RuleEngine.scan(text)
        val settings = Store.settings.value
        val pending = Alert(
            id = recordId ?: UUID.randomUUID().toString(),
            time = recordTime ?: System.currentTimeMillis(),
            appName = appName, pkg = pkg, original = body, sender = sender,
            verdict = "CHECKING", risk = scan.floor, scamType = "", scamTypeLocal = "", summary = "",
            redFlags = scan.hits.filter { it.match.isNotBlank() }.map { RedFlag(it.match, it.label) },
            facts = emptyList(), actions = emptyList(), language = "", source = "on-device",
            localLabels = scan.labels, audioPath = null, status = "checking",
        )
        if (mode != Mode.MANUAL) Store.addAlert(pending)   // shows up in Live Scan right away

        if (mode == Mode.AUTO && !worthChecking(scan, pkg, settings)) {
            val clean = pending.copy(
                verdict = "CLEAN", risk = 0, status = "clean",
                summary = "Kavach's on-device check found no warning signs in this message, so it was not sent to the AI. " +
                    "Open it and tap \"Analyse with AI\" for a full check.",
            )
            Store.addAlert(clean)
            return clean
        }

        val wantVoice = settings.speakAlerts && mode != Mode.MANUAL
        // DEMO gets voice in the same call; AUTO asks for text only and fetches voice later, only for threats.
        val output = if (wantVoice && mode == Mode.DEMO) "both" else "text"
        var alert = try {
            val json = Api.analyze(settings.serverUrl, text, output, settings.replyLanguage)
            Store.countAiCheck()
            fromServer(ctx, json, pending)
        } catch (e: Exception) {
            when {
                mode == Mode.MANUAL -> throw e   // pasted text / re-check: show the error, keep the record as it was
                scan.floor >= 60 || mode == Mode.DEMO -> offline(pending, scan)   // strong on-device signal: still warn
                else -> pending.copy(
                    verdict = "UNCHECKED", status = "error",
                    summary = "Kavach couldn't reach its AI server, so this message has not been judged yet. " +
                        (if (scan.labels.isEmpty()) "The on-device check found no strong warning signs."
                        else "On-device signals: " + scan.labels.take(3).joinToString("; ") + ".") +
                        " Tap \"Analyse with AI\" to try again.",
                )
            }
        }
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

    const val MAX_RECORDING_BYTES = 10 * 1024 * 1024   // Gnani batch direct-upload limit

    /** Name and bytes of a picked/shared audio file. Throws with a readable message if it can't be used. */
    fun readRecording(ctx: Context, uri: Uri): Pair<String, ByteArray> {
        var name = "call_recording.m4a"
        var size = -1L
        ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 }?.let { c.getString(it)?.let { n -> name = n } }
                c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
            }
        }
        if (size > MAX_RECORDING_BYTES) throw IOException("This recording is over 10 MB. Please trim it or pick a shorter call.")
        val bytes = ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: throw IOException("Couldn't open the recording.")
        if (bytes.size > MAX_RECORDING_BYTES) throw IOException("This recording is over 10 MB. Please trim it or pick a shorter call.")
        if (bytes.size < 1000) throw IOException("This file is empty or too short.")
        return name to bytes
    }

    /**
     * Saved call recording -> Gnani Prisma transcript (speakers separated) -> AI verdict, saved as a record.
     * The record appears immediately as "checking" so the user can open it while it is analysed.
     */
    suspend fun processRecording(ctx: Context, name: String, bytes: ByteArray, recordId: String = UUID.randomUUID().toString()): Alert {
        val settings = Store.settings.value
        val pending = Alert(
            id = recordId, time = System.currentTimeMillis(), appName = "Call recording", pkg = "recording",
            original = "Transcribing \"$name\" with Gnani Prisma… long calls can take a minute or two.", sender = name,
            verdict = "CHECKING", risk = 0, scamType = "", scamTypeLocal = "", summary = "",
            redFlags = emptyList(), facts = emptyList(), actions = emptyList(), language = "", source = "on-device",
            localLabels = emptyList(), audioPath = null, status = "checking",
        )
        Store.addAlert(pending)
        val alert = try {
            val json = Api.analyzeAudio(settings.serverUrl, bytes, name, settings.replyLanguage)
            Store.countAiCheck()
            val transcript = json.optJSONObject("input")?.optString("transcript").orEmpty()
            val heard = pending.copy(original = transcript.ifBlank { "(no speech recognised)" })
            fromServer(ctx, json, heard).copy(localLabels = RuleEngine.scan(transcript).labels)
        } catch (e: Exception) {
            pending.copy(
                verdict = "UNCHECKED", status = "error", original = "Recording: $name",
                summary = "Kavach couldn't analyse this recording: ${e.message?.take(160)}. " +
                    "Check that the AI server is reachable, then share or pick the recording again.",
            )
        }
        Store.addAlert(alert)
        return alert
    }

    /** Full AI check of a record that was only checked on the phone (or failed); updates the same record. */
    suspend fun recheck(ctx: Context, a: Alert): Alert? =
        if (a.pkg == "recording" && a.status == "error") throw IOException("Pick or share the recording again to retry.")
        else process(ctx, a.original, a.pkg, a.appName, Mode.MANUAL, a.sender, recordId = a.id, recordTime = a.time)

    private fun fromServer(ctx: Context, json: JSONObject, pending: Alert): Alert {
        val r = json.getJSONObject("result")
        val audioPath = json.optString("audio_b64").takeIf { it.isNotBlank() && it != "null" }?.let { b64 ->
            runCatching {
                val f = File(ctx.filesDir, "voice_${pending.id}.wav")
                f.writeBytes(Base64.decode(b64, Base64.DEFAULT))
                f.absolutePath
            }.getOrNull()
        }
        return pending.copy(
            verdict = r.optString("verdict", "NOT_ENOUGH_INFO"),
            risk = r.optInt("risk_score", pending.risk),
            scamType = r.optString("scam_type"),
            scamTypeLocal = r.optString("scam_type_local"),
            summary = r.optString("summary"),
            redFlags = r.optJSONArray("red_flags").objects().map { RedFlag(it.optString("quote"), it.optString("why")) },
            facts = r.optJSONArray("facts").strings(),
            actions = r.optJSONArray("actions").strings(),
            language = r.optString("language_name", r.optString("language")),
            source = "ai",
            audioPath = audioPath,
            spoken = r.optString("spoken"),
            languageCode = r.optString("language"),
            status = "done",
        )
    }

    private fun offline(pending: Alert, scan: RuleEngine.Scan): Alert {
        val verdict = when {
            scan.floor >= 80 -> "LIKELY_SCAM"
            scan.floor >= 35 -> "SUSPICIOUS"
            else -> "NOT_ENOUGH_INFO"
        }
        return pending.copy(
            verdict = verdict,
            risk = scan.floor,
            summary = "Kavach couldn't reach its AI server, but this message matches known scam patterns: " +
                scan.labels.take(3).joinToString("; ") + ". Don't share OTPs, PINs or money, and don't call numbers in the message.",
            actions = listOf("Don't reply, click links, or call numbers from this message.", "Report fraud on 1930 or cybercrime.gov.in."),
            language = "English",
            source = "on-device",
            status = "offline",
        )
    }

    const val DEMO_TEXT =
        "Dear Consumer, your electricity power will be disconnected tonight at 9.30 PM because your previous " +
            "month bill was not updated. Please immediately contact our electricity officer 98XXXXX310."
}
