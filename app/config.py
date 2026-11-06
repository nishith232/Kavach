import os
from dotenv import load_dotenv

load_dotenv()

# --- Gnani speech ---
GNANI_API_KEY = os.getenv("GNANI_API_KEY", "")
GNANI_BASE = "https://api.vachana.ai"
STT_MODEL = os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
STT_LANGUAGE = os.getenv("GNANI_STT_LANGUAGE", "indic-auto")
TTS_MODEL = os.getenv("GNANI_TTS_MODEL", "timbre-v3.0")
TTS_VOICE = os.getenv("GNANI_TTS_VOICE", "Lakshmi")        # calm, reassuring voice for verdicts

# Audio up to this length goes to the fast REST endpoint; longer goes to batch (with speaker separation).
REST_MAX_SECONDS = 28
BATCH_POLL_SECONDS = 3
BATCH_TIMEOUT_SECONDS = 180

# --- LLM (any OpenAI-compatible endpoint; Groq by default) ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Domain words that help the speech recogniser on noisy scam calls.
KEYTERMS = [
    "CBI", "ED", "NCB", "RBI", "TRAI", "customs", "FedEx", "DHL", "parcel", "courier",
    "digital arrest", "arrest warrant", "money laundering", "Aadhaar", "PAN", "KYC", "OTP", "UPI",
    "AnyDesk", "TeamViewer", "Skype", "video call", "Mumbai police", "cyber crime", "SIM block",
    "electricity bill", "lottery", "refund", "investment", "IPO", "trading", "WhatsApp group",
]
