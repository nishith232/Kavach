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
    (r"\bkyc\b|केवाईसी|కేవైసీ|ಕೆವೈಸಿ|account (will be |is )?(block|suspend|frozen|freez)|अकाउंट (ब्लॉक|बंद)|బ్లాక్ అవుతుంది|ಬ್ಲಾಕ್ ಆಗ", 2, "KYC update / account block threat"),
    (r"reversal code|verification code|security code|read (it|the code|that) (out|to me)|code .{0,20}read", 3, "Asks you to read out a code sent to your phone"),
    (r"warna|वरना|otherwise we|or else|ఇల్లేకపోతే|లేకపోతే|ಇಲ್ಲದಿದ್ದರೆ|இல்லையென்றால்", 2, "Threat: do this or else"),
    (r"parcel|courier|fedex|dhl|पार्सल|పార్సెల్|ಪಾರ್ಸೆಲ್", 2, "Parcel / courier story"),
    (r"drugs?|ड्रग्स|నార్కోటిక్|narcotic|mdma", 2, "Claims drugs were found"),
    (r"aadhaar|aadhar|आधार|ఆధార్|ಆಧಾರ್|ஆதார்", 1, "Mentions Aadhaar misuse"),
    (r"don'?t\s*tell|do not tell|keep (this|it) secret|किसी को (मत|ना) बता|ఎవరికీ చెప్పొద్దు|ಯಾರಿಗೂ ಹೇಳಬೇಡ", 3, "Demands secrecy"),
    (r"video\s*call|वीडियो\s*कॉल|వీడియో\s*కాల్|skype", 2, "Moves you to a video call"),
    (r"transfer|send (the )?money|ट्रांसफर|पैसे भेज|డబ్బు పంపండి|ట్రాన్స్‌?ఫర్|ವರ್ಗಾವಣೆ|safe\s*account|सेफ\s*अकाउंट|verification\s*account|rbi account|deposit", 3, "Asks you to transfer or deposit money"),
    (r"police case|fir\b|पुलिस (केस|कंप्लेंट)|పోలీస్ కేసు|ಪೊಲೀಸ್ ಕೇಸ್|போலீஸ் வழக்கு", 2, "Threatens a police case"),
    (r"install (the |our |this )?\w*\s*app|download (the |our )?\w*\s*app|ऐप (डाउनलोड|इंस्टॉल)|डाउनलोड करके|download karke|యాప్ (డౌన్‌?లోడ్|ఇన్‌?స్టాల్)", 2, "Asks you to install an app"),
    (r"like kar|daily \d{3,}|रोज़? \d{3,}|kamaye|kamao|ghar baithe", 2, "Easy-money job offer"),
    (r"\bfine\b|penalty|जुर्माना|జరిమానా", 2, "Demands a fine or penalty"),
    (r"(sim|mobile number|number) (will be )?(block|deactivat|band)|सिम (बंद|ब्लॉक)|trai", 2, "Threatens to block SIM (TRAI story)"),
    (r"electricity|bijli|बिजली|కరెంట్|విద్యుత్|ವಿದ್ಯುತ್|மின்|power (will be )?(cut|disconnected)|meter update|मीटर अपडेट|कनेक्शन कट|connection (will be )?cut", 2, "Electricity disconnection threat"),
    (r"lottery|prize|you (have )?won|लॉटरी|इनाम|లాటరీ|బహుమతి", 2, "Prize / lottery claim"),
    (r"guarantee[d]? (return|profit)|double (your )?money|\d+\s*%\s*(daily|monthly|return)|ipo allotment", 3, "Guaranteed / unrealistic returns"),
    (r"whatsapp group|telegram|trading app|stock tip", 1, "Investment group / app"),
    (r"task|like and earn|review and earn|part[-\s]?time job|work from home", 1, "Task / part-time job offer"),
    (r"refund|cashback|रिफंड", 1, "Refund / cashback offer"),
    (r"right now|immediately|urgent|within (\d+|one|two) (minutes?|hours?)|तुरंत|अभी|వెంటనే|ತಕ್ಷಣ", 2, "Creates urgency"),
    (r"https?://|bit\.ly|tinyurl|\.apk\b", 2, "Contains a link or app file"),
    (r"scan (the )?qr|qr code|collect request|क्यूआर|స్కాన్|క్యూఆర్|ಕ್ಯೂಆರ್|ಸ್ಕ್ಯಾನ್|ரிக்வெஸ்ட்|अप्रूव|రిక్వెస్ట్", 2, "QR / UPI collect request"),
    (r"ಪಿನ್|பின்|पिन डाल|enter (your )?(upi )?pin", 3, "Asks you to enter your UPI PIN"),
    (r"processing fee|registration fee|insurance fee|gst pehle|fee (pehle|first|before)|फीस (पहले|जमा)|జీఎస్టీ .{0,30}కట్టాలి|ఫీజు .{0,20}(కట్టాలి|కట్టండి)|ముందుగా కట్టాలి|ಶುಲ್ಕ .{0,20}(ಪಾವತಿಸಿ|ಕಟ್ಟಿ)|கட்டணம் .{0,20}(செலுத்த|கட்ட)", 3, "Asks for a fee before paying you (advance fee)"),
    (r"you (have )?won|jeete|जीते|गेलि|గెలిచారు|ಗೆದ್ದಿದ್ದೀರಿ|வென்ற|lucky draw|लकी ड्रॉ|లక్కీ డ్రా|kbc", 2, "Says you won a prize / lucky draw"),
    (r"double|दोगुना|రెట్టింపు|ದ್ವಿಗುಣ|இரட்டிப்பு|guarantee|गारंटी|గ్యారంటీ|ಖಾತರಿ|உத்தரவாதம்", 2, "Promises guaranteed or doubled money"),
    (r"withdraw|विड्रॉल|निकाल|tax .{0,30}(before|to) withdraw|टैक्स", 2, "Must pay to withdraw your own money"),
    (r"loan app|instant loan|cashnow|pre-?approved|no cibil|लोन|లోన్|ಸಾಲ|கடன்", 2, "Loan offer / loan app"),
    (r"morphed|morph|contacts ko|contacts (and|aur) family|सारे कॉन्टैक्ट|కాంటాక్ట్స్|ಕಾಂಟ್ಯಾಕ್ಟ್", 3, "Threatens to message your contacts / morphed photos"),
    (r"video viral|viral kar|obscene|nude|अश्लील|न्यूड|screen recording|आत्महत्या", 3, "Threatens to leak an intimate video"),
    (r"new number|naya number|नया नंबर|kotha number|కొత్త నంబర్|phone fell|mic is not working|don'?t call", 2, "'New number' / don't call me back"),
    (r"accident|एक्सीडेंट|ఆక్సిడెంట్|ಅಪಘಾತ|airport|ఎయిర్‌పోర్ట్|immigration|ఇమ్మిగ్రేషన్|jail|జైలు|जेल", 2, "Relative in trouble / emergency story"),
    (r"review|రివ్యూ|రేటింగ్|ರಿವ್ಯೂ|rating|google maps|గూగుల్ మ్యాప్స్", 1, "Paid reviews / ratings"),
    (r"సంపాదించ|ಸಂಪಾದಿಸ|சம்பாதி|kamao|kamaye|कमाएं|कमाओ|earn (rs|₹|\d)", 2, "Easy earnings promise"),
    (r"ಗಿಫ್ಟ್|గిఫ్ట్|gift parcel|custom(s)? duty|ಕಸ್ಟಮ್ಸ್|కస్టమ్స్|कस्टम", 2, "Gift parcel / customs duty"),
    (r"ఈ నంబర్‌కి|ఈ అకౌంట్|ಈ ಯುಪಿಐ|इस नंबर पर|is number pe|this account", 2, "Send money to a given number / account"),
]
_COMPILED = [(re.compile(p, re.I), w, label) for p, w, label in _RULES]


# "We will never ask for your OTP" / "Do not share this OTP" are protective, not red flags.
_PROTECTIVE = re.compile(
    r"(never|not|n't)\s+(ask|share|call)|do not share|don'?t share|never share|"
    r"कभी (भी )?नहीं|शेयर न करें|साझा न करें|ఎప్పుడూ అడగ|షేర్ చేయవద్దు|ಎಂದಿಗೂ ಕೇಳ|பகிர வேண்டாம்", re.I)
_PROTECTED_LABELS = {"Asks about an OTP", "Asks for PIN / CVV"}
_QUESTION = re.compile(r"^(do|does|is|are|can|will|should|what|how|why|kya|क्या|ఏ|ಏನು)\b.*\?\s*$", re.I | re.S)


def scan(text: str, segments: list[dict] | None = None) -> dict:
    """Return matched red flags and a risk floor (0-90) the LLM's score can't go below."""
    hits, seen = [], set()
    protective = bool(_PROTECTIVE.search(text))
    asks_otp = re.search(r"(share|tell|give|read|bata|batao|చెప్పండి|ಹೇಳಿ|சொல்லுங்கள்)\W+(\w+\W+){0,3}(otp|ओटीपी|ఓటీపీ|ಒಟಿಪಿ|pin)|"
                         r"(otp|ओटीपी|ఓటీపీ|ಒಟಿಪಿ|pin|code)\W+(\w+\W+){0,4}(share|tell|bata|read|చెప్పండి|ಹೇಳಿ)", text, re.I)
    for rx, weight, label in _COMPILED:
        if protective and not asks_otp and label in _PROTECTED_LABELS:
            continue
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
    # A short general question ("Do police arrest people on video calls?") is not itself a scam.
    if len(text) < 200 and _QUESTION.match(text.strip()) and strong == 0:
        floor = 0
    return {"hits": hits, "score": score, "risk_floor": floor}


def knowledge_block() -> str:
    pb = "\n".join(f"- {name}: {desc}" for name, desc in PLAYBOOKS.items())
    facts = "\n".join(f"- {f}" for f in OFFICIAL_FACTS)
    return f"KNOWN SCAM PLAYBOOKS (India):\n{pb}\n\nVERIFIED FACTS YOU MAY CITE:\n{facts}"
