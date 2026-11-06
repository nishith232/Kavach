package app.kavach.guard.core

import android.content.Context
import org.json.JSONObject
import java.util.regex.Pattern

/**
 * On-device keyword scan: the same rules as the server (app/scam_kb.py), exported to
 * assets/rules.json and refreshed from GET /api/rules. Runs on every notification so that
 * only suspicious messages ever leave the phone.
 */
object RuleEngine {
    private const val FLAGS = Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE or Pattern.UNICODE_CHARACTER_CLASS

    data class Rule(val pattern: Pattern, val weight: Int, val label: String)
    data class Hit(val label: String, val match: String, val weight: Int)
    data class Scan(val hits: List<Hit>, val score: Int, val floor: Int) {
        val labels: List<String> get() = hits.map { it.label }
    }

    @Volatile private var rules: List<Rule> = emptyList()
    @Volatile private var protective: Pattern? = null
    @Volatile private var asksOtp: Pattern? = null
    @Volatile private var question: Pattern? = null
    @Volatile private var protectedLabels: Set<String> = emptySet()

    val ruleCount: Int get() = rules.size

    fun init(ctx: Context) {
        val bundled = ctx.assets.open("rules.json").bufferedReader().use { it.readText() }
        val cached = Store.cachedRules()
        if (cached == null || runCatching { load(cached) }.isFailure) load(bundled)
    }

    /** Parse and swap in a rules JSON. Throws if invalid (caller keeps the old rules). */
    fun load(json: String) {
        val o = JSONObject(json)
        val arr = o.getJSONArray("rules")
        val parsed = (0 until arr.length()).map {
            val r = arr.getJSONObject(it)
            Rule(Pattern.compile(r.getString("pattern"), FLAGS), r.getInt("weight"), r.getString("label"))
        }
        val labels = o.getJSONArray("protected_labels")
        val newProtective = Pattern.compile(o.getString("protective"), FLAGS)
        val newAsks = Pattern.compile(o.getString("asks_otp"), FLAGS)
        val newQuestion = Pattern.compile(o.getString("question"), FLAGS or Pattern.DOTALL)
        protectedLabels = (0 until labels.length()).map { labels.getString(it) }.toSet()
        protective = newProtective
        asksOtp = newAsks
        question = newQuestion
        rules = parsed
    }

    fun scan(text: String): Scan {
        val isProtective = protective?.matcher(text)?.find() == true
        val asks = asksOtp?.matcher(text)?.find() == true
        val hits = mutableListOf<Hit>()
        val seen = HashSet<String>()
        for (r in rules) {
            if (isProtective && !asks && r.label in protectedLabels) continue
            val m = r.pattern.matcher(text)
            if (m.find() && seen.add(r.label)) hits += Hit(r.label, m.group(), r.weight)
        }
        val score = hits.sumOf { it.weight }
        val strong = hits.count { it.weight == 3 }
        var floor = when {
            strong >= 2 || score >= 9 -> 80
            strong >= 1 && score >= 5 -> 60
            score >= 4 -> 35
            else -> 0
        }
        if (text.length < 200 && strong == 0 && question?.matcher(text.trim())?.matches() == true) floor = 0
        return Scan(hits, score, floor)
    }
}
