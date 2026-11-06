package app.kavach.guard.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Talks to the Kavach FastAPI server (POST /api/message, GET /api/rules, GET /health). */
object Api {
    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)   // AI + voice can take a few seconds
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private fun base(url: String) = url.trim().trimEnd('/').let { if (it.startsWith("http")) it else "http://$it" }

    suspend fun analyze(server: String, text: String, output: String, replyLanguage: String): JSONObject =
        withContext(Dispatchers.IO) {
            val body = MultipartBody.Builder().setType(MultipartBody.FORM)
                .addFormDataPart("text", text)
                .addFormDataPart("output", output)
                .addFormDataPart("reply_language", replyLanguage)
                .build()
            val req = Request.Builder().url("${base(server)}/api/message").post(body).build()
            client.newCall(req).execute().use { resp ->
                val raw = resp.body?.string().orEmpty()
                val json = runCatching { JSONObject(raw) }.getOrNull()
                    ?: throw IOException("Server returned ${resp.code}: ${raw.take(120)}")
                if (json.has("error")) throw IOException(json.optString("error"))
                json
            }
        }

    suspend fun health(server: String): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(Request.Builder().url("${base(server)}/health").build()).execute().use { it.isSuccessful }
        }.getOrDefault(false)
    }

    suspend fun rules(server: String): String? = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(Request.Builder().url("${base(server)}/api/rules").build()).execute().use {
                if (it.isSuccessful) it.body?.string() else null
            }
        }.getOrNull()
    }
}
