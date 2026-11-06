"""Single source of truth for every language the voice pipeline supports.

Speech in/out is limited by Gnani: Prisma STT and Timbre TTS cover 10 Indian
languages + English, and Timbre adds 'hi-en' (Hinglish). The LLM itself handles
all of these natively, so text is never translated to English along the way.
"""
import re

LANGUAGES = {
    #  code     name          script regex                     "sorry, say again" fallback
    "en-IN": ("English",   r"[A-Za-z]",               "Sorry, I didn't catch that. Please say it again."),
    "hi-IN": ("Hindi",     r"[ऀ-ॿ]",        "माफ़ कीजिए, कृपया फिर से बोलिए।"),
    "hi-en": ("Hinglish",  r"[A-Za-z]",               "Sorry, samajh nahi aaya. Please dobara boliye."),
    "te-IN": ("Telugu",    r"[ఀ-౿]",        "క్షమించండి, మళ్ళీ చెప్పండి."),
    "kn-IN": ("Kannada",   r"[ಀ-೿]",        "ಕ್ಷಮಿಸಿ, ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ."),
    "ta-IN": ("Tamil",     r"[஀-௿]",        "மன்னிக்கவும், மீண்டும் சொல்லுங்கள்."),
    "ml-IN": ("Malayalam", r"[ഀ-ൿ]",        "ക്ഷമിക്കണം, ഒന്നുകൂടി പറയാമോ?"),
    "mr-IN": ("Marathi",   r"[ऀ-ॿ]",        "माफ करा, कृपया पुन्हा सांगा."),
    "bn-IN": ("Bengali",   r"[ঀ-৿]",        "দুঃখিত, আবার বলুন।"),
    "gu-IN": ("Gujarati",  r"[઀-૿]",        "માફ કરશો, ફરીથી કહો."),
    "pa-IN": ("Punjabi",   r"[਀-੿]",        "ਮਾਫ਼ ਕਰਨਾ, ਦੁਬਾਰਾ ਦੱਸੋ।"),
}

NAMES = {code: v[0] for code, v in LANGUAGES.items()}
_SCRIPT_RX = {code: re.compile(v[1]) for code, v in LANGUAGES.items()
              if code not in ("hi-en", "mr-IN")}  # these share scripts with en-IN / hi-IN


def name(code: str | None) -> str:
    return NAMES.get(code or "", "the caller's language")


def fallback(code: str | None) -> str:
    return LANGUAGES.get(code or "", LANGUAGES["en-IN"])[2]


def normalise(code: str | None) -> str | None:
    """'TE-in' -> 'te-IN', 'hi-EN' -> 'hi-en', junk -> None."""
    if not code:
        return None
    c = code.strip().lower()
    if c in ("hi-en", "hinglish"):
        return "hi-en"
    c = c[:2] + "-IN" if len(c) >= 2 else c
    return c if c in LANGUAGES else None


def script_of(text: str) -> str | None:
    """Language code whose script dominates the text ('en-IN' for Latin), or None."""
    counts = {code: len(rx.findall(text)) for code, rx in _SCRIPT_RX.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else None


# Reply tag the LLM puts on the first line, e.g. "<lang>te-IN</lang>"
TAG_RE = re.compile(r"^\s*<lang>\s*([A-Za-z]{2}-[A-Za-z]{2})\s*</lang>\s*", re.I)


def split_tag(text: str) -> tuple[str | None, str]:
    m = TAG_RE.match(text)
    if not m:
        return None, text.strip()
    return normalise(m.group(1)), text[m.end():].strip()
