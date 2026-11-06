"""Scam knowledge base + a fast, explainable keyword scan.

The LLM does the real reasoning; this module gives it (1) the known Indian scam
playbooks and verified facts to cite, and (2) deterministic red-flag signals that
also set a minimum risk score, so an obvious scam can never be scored "safe".
"""
import re

OFFICIAL_FACTS = [
    "There is no such thing as 'digital arrest' in Indian law. Police, CBI, ED, NCB or customs never arrest anyone over a phone or video call.",
    "Government agencies never ask you to transfer money to a 'safe' or 'verification' account, or to pay a fine over UPI.",
    "Banks and the RBI never ask for your OTP, UPI PIN, CVV or passwords. Anyone asking for these is a fraudster.",
    "Real officials never tell you to keep the call secret from your family or to stay on a video call for hours.",
    "Never install screen-sharing apps (AnyDesk, TeamViewer, QuickSupport) because a caller asked you to.",
    "Report cyber fraud immediately on the national helpline 1930 or at cybercrime.gov.in. Reporting within the first hours gives the best chance to freeze the money.",
    "Report suspected fraud calls and messages on the government's Sanchar Saathi portal (Chakshu).",
    "Guaranteed high returns, 'insider' stock tips in WhatsApp or Telegram groups, and 'tasks' that pay for likes or reviews are classic investment and job scams.",
]

PLAYBOOKS = {
    "Digital arrest / fake police": "Caller claims to be CBI, ED, NCB, customs, TRAI or police; says your Aadhaar/SIM/parcel is linked to a crime; threatens arrest; moves you to a video call; demands secrecy; asks for money to 'verify' or settle.",
    "Courier / parcel scam": "Says a parcel in your name has drugs, passports or contraband (often FedEx/DHL); connects you to 'police'; ends in digital arrest or payment.",
    "Bank / KYC / OTP fraud": "Says your account/card/KYC will be blocked; asks for OTP, PIN, card details, or to click a link or install an app.",
    "Investment / trading scam": "WhatsApp/Telegram group, fake trading app, guaranteed or very high returns, 'IPO allotment', pressure to invest more before withdrawing.",
    "Task / job scam": "Paid for likes, reviews or simple tasks; small payouts first, then asks you to 'deposit' to unlock bigger earnings.",
    "Electricity / bill disconnection": "Says power or gas will be cut tonight unless you pay or call a number; links to pay.",
    "Lottery / prize / refund": "You won a prize, cashback or tax/insurance refund but must pay a fee or share details to claim.",
    "Relative-in-trouble / voice clone": "Urgent call from a 'relative' or 'friend' (voice may be AI-cloned) who needs money immediately; asks not to tell others.",
    "Sextortion": "Video call with explicit content, then threats to leak a recording unless you pay.",
    "Loan app harassment": "Instant loan app with hidden charges; threats and harassment of contacts for repayment.",
    "UPI collect / QR scam": "Asks you to 'scan to receive money' or approve a collect request; entering your PIN actually sends money.",
}

# (pattern, weight, label). Weight 3 = strong scam marker, 2 = suspicious, 1 = context.
# Includes English, romanised Hindi, and common Devanagari/Telugu/Kannada/Tamil spellings.
_RULES = [
    (r"digital\s*arrest|डिजिटल\s*अरेस्ट|డిజిటల్\s*అరెస్ట్", 3, "Mentions 'digital arrest' (does not exist in law)"),
    (r"\b(cbi|ncb|enforcement directorate|\bed\b officer)|सीबीआई|సీబీఐ|ಸಿಬಿಐ", 2, "Claims to be a central agency (CBI/NCB/ED)"),
    (r"arrest\s*warrant|गिरफ्तार|गिरफ़्तार|అరెస్ట్|ಬಂಧನ|கைது|warrant", 2, "Threat of arrest"),
    (r"money\s*laundering|मनी\s*लॉन्ड्रिंग|హవాలా|hawala", 3, "Accuses you of money laundering"),
    (r"\botp\b|ओटीपी|ఓటీపీ|ಒಟಿಪಿ|ஓடிபி|one.?time.?password", 3, "Asks about an OTP"),
    (r"upi\s*pin|\bpin\b|cvv|पिन|పిన్", 3, "Asks for PIN / CVV"),
    (r"anydesk|any\s*desk|teamviewer|quick\s*support|screen\s*shar", 3, "Asks to install a screen-sharing app"),
    (r"\bkyc\b|केवाईसी|కేవైసీ|ಕೆವೈಸಿ", 2, "KYC update / account block threat"),
    (r"parcel|courier|fedex|dhl|पार्सल|పార్సెల్|ಪಾರ್ಸೆಲ್", 2, "Parcel / courier story"),
    (r"drugs?|ड्रग्स|నార్కోటిక్|narcotic|mdma", 2, "Claims drugs were found"),
    (r"aadhaar|aadhar|आधार|ఆధార్|ಆಧಾರ್|ஆதார்", 1, "Mentions Aadhaar misuse"),
    (r"don'?t\s*tell|do not tell|keep (this|it) secret|किसी को (मत|ना) बता|ఎవరికీ చెప్పొద్దు|ಯಾರಿಗೂ ಹೇಳಬೇಡ", 3, "Demands secrecy"),
    (r"video\s*call|वीडियो\s*कॉल|వీడియో\s*కాల్|skype", 2, "Moves you to a video call"),
    (r"transfer|send (the )?money|ट्रांसफर|पैसे भेज|డబ్బు పంపండి|ట్రాన్స్‌?ఫర్|ವರ್ಗಾವಣೆ|safe\s*account|सेफ\s*अकाउंट|verification\s*account|rbi account|deposit", 3, "Asks you to transfer or deposit money"),
    (r"police case|fir\b|पुलिस (केस|कंप्लेंट)|పోలీస్ కేసు|ಪೊಲೀಸ್ ಕೇಸ್|போலீஸ் வழக்கு", 2, "Threatens a police case"),
    (r"install (the |our |this )?\w*\s*app|download (the |our )?\w*\s*app|ऐप (डाउनलोड|इंस्टॉल)|యాప్ (డౌన్‌?లోడ్|ఇన్‌?స్టాల్)", 2, "Asks you to install an app"),
    (r"like kar|daily \d{3,}|रोज़? \d{3,}|kamaye|kamao|ghar baithe", 2, "Easy-money job offer"),
    (r"\bfine\b|penalty|जुर्माना|జరిమానా", 2, "Demands a fine or penalty"),
    (r"(sim|mobile number|number) (will be )?(block|deactivat|band)|सिम (बंद|ब्लॉक)|trai", 2, "Threatens to block SIM (TRAI story)"),
    (r"electricity|bijli|बिजली|కరెంట్ బిల్|disconnect", 2, "Electricity disconnection threat"),
    (r"lottery|prize|you (have )?won|लॉटरी|इनाम|లాటరీ|బహుమతి", 2, "Prize / lottery claim"),
    (r"guarantee[d]? (return|profit)|double (your )?money|\d+\s*%\s*(daily|monthly|return)|ipo allotment", 3, "Guaranteed / unrealistic returns"),
    (r"whatsapp group|telegram|trading app|stock tip", 1, "Investment group / app"),
    (r"task|like and earn|review and earn|part[-\s]?time job|work from home", 1, "Task / part-time job offer"),
    (r"refund|cashback|रिफंड", 1, "Refund / cashback offer"),
    (r"right now|immediately|urgent|within (\d+|one|two) (minutes?|hours?)|तुरंत|अभी|వెంటనే|ತಕ್ಷಣ", 2, "Creates urgency"),
    (r"https?://|bit\.ly|tinyurl|\.apk\b", 2, "Contains a link or app file"),
    (r"scan (the )?qr|qr code|collect request", 2, "QR / UPI collect request"),
]
_COMPILED = [(re.compile(p, re.I), w, label) for p, w, label in _RULES]


def scan(text: str, segments: list[dict] | None = None) -> dict:
    """Return matched red flags and a risk floor (0-90) the LLM's score can't go below."""
    hits, seen = [], set()
    for rx, weight, label in _COMPILED:
        m = rx.search(text)
        if m and label not in seen:
            seen.add(label)
            hits.append({"label": label, "match": m.group(0), "weight": weight})

    # Emotional pressure from batch STT: fear/anger/urgency in the caller's segments.
    emotions = [str(s.get("emotion") or "").lower() for s in (segments or [])]
    pressure = sum(e in ("fear", "anger", "angry", "fearful", "anxious", "urgent") for e in emotions)
    if pressure >= 2:
        hits.append({"label": f"Emotional pressure detected in {pressure} segments", "match": "", "weight": 1})

    score = sum(h["weight"] for h in hits)
    strong = sum(h["weight"] == 3 for h in hits)
    floor = 0
    if strong >= 2 or score >= 9:
        floor = 80
    elif strong >= 1 and score >= 5:
        floor = 60
    elif score >= 4:
        floor = 35
    return {"hits": hits, "score": score, "risk_floor": floor}


def knowledge_block() -> str:
    pb = "\n".join(f"- {name}: {desc}" for name, desc in PLAYBOOKS.items())
    facts = "\n".join(f"- {f}" for f in OFFICIAL_FACTS)
    return f"KNOWN SCAM PLAYBOOKS (India):\n{pb}\n\nVERIFIED FACTS YOU MAY CITE:\n{facts}"
