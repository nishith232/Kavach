package app.kavach.guard.core

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Base64
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/** Records the microphone as 16 kHz mono 16-bit PCM and returns a WAV (what Gnani Prisma REST expects). */
class VoiceRecorder {
    companion object {
        const val RATE = 16_000
        const val MAX_SECONDS = 15
    }

    private var record: AudioRecord? = null
    private var job: Job? = null
    private val pcm = ByteArrayOutputStream()

    /** 0..1 loudness of the latest buffer, for the "listening" animation. */
    @Volatile var level: Float = 0f
        private set

    val seconds: Float get() = synchronized(pcm) { pcm.size() / (RATE * 2f) }

    /** Requires RECORD_AUDIO (the screen asks for it first). */
    @SuppressLint("MissingPermission")
    fun start(scope: CoroutineScope, onLimit: () -> Unit) {
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = AudioRecord(
            MediaRecorder.AudioSource.MIC, RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            maxOf(min, 8192),
        )
        check(r.state == AudioRecord.STATE_INITIALIZED) { "Microphone is not available" }
        synchronized(pcm) { pcm.reset() }
        r.startRecording()
        record = r
        job = scope.launch(Dispatchers.IO) {
            val buf = ByteArray(3200)   // 100 ms
            while (isActive) {
                val n = r.read(buf, 0, buf.size)
                if (n <= 0) continue
                synchronized(pcm) { pcm.write(buf, 0, n) }
                level = rms(buf, n)
                if (seconds >= MAX_SECONDS) {
                    onLimit()
                    break
                }
            }
        }
    }

    /** Stop and return the recording as WAV bytes. */
    suspend fun stop(): ByteArray {
        job?.cancelAndJoin()
        job = null
        record?.let { runCatching { it.stop() }; it.release() }
        record = null
        level = 0f
        return wav(synchronized(pcm) { pcm.toByteArray() })
    }

    fun cancel() {
        job?.cancel()
        record?.let { runCatching { it.stop() }; it.release() }
        record = null
    }

    private fun rms(buf: ByteArray, n: Int): Float {
        val bb = ByteBuffer.wrap(buf, 0, n).order(ByteOrder.LITTLE_ENDIAN)
        var sum = 0.0
        var count = 0
        while (bb.remaining() >= 2) {
            val v = bb.short / 32768.0
            sum += v * v
            count++
        }
        return if (count == 0) 0f else minOf(1f, (sqrt(sum / count) * 4).toFloat())
    }

    private fun wav(data: ByteArray): ByteArray {
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(36 + data.size); put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1); putInt(RATE); putInt(RATE * 2)
            putShort(2); putShort(16); put("data".toByteArray()); putInt(data.size)
        }
        return header.array() + data
    }
}

/** One answer from the Kavach voice assistant. */
data class AssistantReply(
    val transcript: String,
    val heardByGnani: Boolean,
    val intent: String,
    val reply: String,
    val languageName: String,
    val recordIds: List<String>,
    val audioPath: String?,
    val ttsError: String?,
)

object VoiceAssistant {
    val QUICK_COMMANDS = listOf(
        "Last hour" to "Check my messages from the last hour",
        "Suspicious" to "Show my suspicious messages",
        "Genuine" to "Show my genuine messages",
        "Latest alerts" to "Read my latest security alerts",
        "Summary" to "Give me a summary of my scanned messages",
        "Explain" to "Explain why this message is suspicious",
    )

    /** Send a spoken (wav) or typed command; the reply's voice is saved to a cache file for playback. */
    suspend fun ask(ctx: Context, wav: ByteArray?, text: String?, focusId: String? = null): AssistantReply {
        val settings = Store.settings.value
        val json = Api.voiceCommand(settings.serverUrl, wav, text, Store.assistantRecords(), focusId, settings.replyLanguage)
        val audio = json.optString("audio_b64").takeIf { it.isNotBlank() && it != "null" }?.let { b64 ->
            withContext(Dispatchers.IO) {
                runCatching {
                    Notifier.stopSpeaking()
                    File(ctx.cacheDir, "assistant_reply.wav").apply { writeBytes(Base64.decode(b64, Base64.DEFAULT)) }.absolutePath
                }.getOrNull()
            }
        }
        val ids = json.optJSONArray("record_ids")
        return AssistantReply(
            transcript = json.optString("transcript"),
            heardByGnani = json.optString("heard_by") == "gnani-prisma",
            intent = json.optString("intent"),
            reply = json.optString("reply"),
            languageName = json.optString("language_name"),
            recordIds = if (ids == null) emptyList() else (0 until ids.length()).map { ids.optString(it) },
            audioPath = audio,
            ttsError = json.optString("tts_error").takeIf { it.isNotBlank() && it != "null" },
        )
    }
}
