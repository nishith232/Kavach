package app.kavach.guard.core

import android.content.Context
import org.json.JSONObject
import java.util.regex.Pattern

/**
 * On-device keyword scan: the same rules AND the same algorithm as the server (app/scam_kb.py),
 * exported to assets/rules.json and refreshed from GET /api/rules. Runs on every notification so
 * that only suspicious messages ever leave the phone.
 */
object RuleEngine {
    // Android's regex engine (ICU) already treats \w and \b as Unicode-aware (Telugu, Hindi, Tamil...).
    // It rejects Pattern.UNICODE_CHARACTER_CLASS with IllegalArgumentException, so don't pass it.
    private const val FLAGS = Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE

    /** Rules that failed to compile on this device (shown in Settings for debugging). */
    @Volatile var skipped: List<String> = emptyList()
        private set

    data class Rule(val pattern: Pattern, val weight: Int, val label: String, val family: String, val masked: Boolean)
    data class Hit(val label: String, val match: String, val weight: Int, val family: String = label)
    data class Scan(val hits: List<Hit>, val score: Int, val floor: Int) {
        val labels: List<String> get() = hits.map { it.label }
    }

    private class Config(
        val rules: List<Rule>,
        val sentence: Pattern, val clause: Pattern, val negation: Pattern, val verbs: Pattern,
        val credential: Pattern, val guard: Pattern, val transaction: Pattern, val question: Pattern,
        val askFamilies: Set<String>,
    )

    @Volatile private var cfg: Config? = null

    val ruleCount: Int get() = cfg?.rules?.size ?: 0

    /** Never throws: a broken rules file must not crash the app. */
    fun init(ctx: Context) {
        val cached = Store.cachedRules()
        if (cached != null && runCatching { load(cached) }.isSuccess) return
        runCatching { load(ctx.assets.open("rules.json").bufferedReader().use { it.readText() }) }
    }

    /** Parse and swap in a rules JSON (version 2+). Throws if invalid (caller keeps the old rules). */
    fun load(json: String) {
        val o = JSONObject(json)
        require(o.optInt("version", 1) >= 2) { "rules version ${o.optInt("version", 1)} is too old" }
        val arr = o.getJSONArray("rules")
        val bad = mutableListOf<String>()
        val parsed = (0 until arr.length()).mapNotNull {
            val r = arr.getJSONObject(it)
            runCatching {
                Rule(
                    Pattern.compile(r.getString("pattern"), FLAGS), r.getInt("weight"), r.getString("label"),
                    r.optString("family", r.getString("label")), r.optBoolean("masked", false),
                )
            }.onFailure { e -> bad += "${r.optString("label")}: ${e.message?.take(80)}" }.getOrNull()
        }
        if (parsed.isEmpty()) throw IllegalStateException("No rules compiled: ${bad.firstOrNull()}")
        val m = o.getJSONObject("mask")
        val asks = o.getJSONArray("ask_families")
        cfg = Config(
            rules = parsed,
            sentence = Pattern.compile(m.getString("sentence"), FLAGS),
            clause = Pattern.compile(m.getString("clause"), FLAGS),
            negation = Pattern.compile(m.getString("negation"), FLAGS),
            verbs = Pattern.compile(m.getString("verbs"), FLAGS),
            credential = Pattern.compile(m.getString("credential"), FLAGS),
            guard = Pattern.compile(m.getString("guard"), FLAGS),
            transaction = Pattern.compile(o.getString("transaction"), FLAGS),
            question = Pattern.compile(o.getString("question"), FLAGS or Pattern.DOTALL),
            askFamilies = (0 until asks.length()).map { asks.getString(it) }.toSet(),
        )
        skipped = bad
    }

    /** Blank out clauses that WARN about sharing credentials ("do not share this OTP"), same as the server. */
    private fun mask(text: String, c: Config): String {
        val out = StringBuilder(text)
        val sm = c.sentence.matcher(text)
        while (sm.find()) {
            val sentence = sm.group()
            if (c.guard.matcher(sentence).find()) continue
            val cm = c.clause.matcher(sentence)
            while (cm.find()) {
                val clause = cm.group()
                if (c.negation.matcher(clause).find() && c.verbs.matcher(clause).find() && c.credential.matcher(clause).find()) {
                    for (i in sm.start() + cm.start() until sm.start() + cm.end()) out.setCharAt(i, ' ')
                }
            }
        }
        return out.toString()
    }

    fun scan(text: String): Scan {
        val c = cfg ?: return Scan(emptyList(), 0, 0)
        val masked = mask(text, c)
        val best = LinkedHashMap<String, Hit>()
        for (r in c.rules) {
            val m = r.pattern.matcher(if (r.masked) masked else text)
            if (m.find()) {
                val prev = best[r.family]
                if (prev == null || r.weight > prev.weight) best[r.family] = Hit(r.label, m.group().trim(), r.weight, r.family)
            }
        }
        if ("cred_ask" in best) best.remove("cred_mention")
        val hits = best.values.toList()
        val score = hits.sumOf { it.weight }
        val strong = hits.count { it.weight == 3 }
        val families = hits.map { it.family }.toSet()
        val asks = families.any { it in c.askFamilies }
        var floor = when {
            strong >= 2 -> 80
            strong >= 1 && score >= 10 -> 80
            strong >= 1 && score >= 5 -> 60
            score >= 8 && asks && families.size >= 4 -> 60
            score >= 4 && families.size >= 2 -> 35
            else -> 0
        }
        if (!asks && c.transaction.matcher(text).find()) floor = 0
        if (text.length < 200 && strong == 0 && c.question.matcher(text.trim()).matches()) floor = 0
        return Scan(hits, score, floor)
    }
}
