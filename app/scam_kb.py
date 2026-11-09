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

# (pattern, weight, label, family). Weight 3 = strong scam marker, 2 = suspicious, 1 = context only.
# Rules in the same family describe the same signal, so a family counts once (its highest weight):
# "you won" / "lucky draw" / "lottery" is one lure, not three.
# English, romanised Hindi (Hinglish) and common Devanagari/Telugu/Kannada/Tamil spellings.
# Patterns must also compile on Android (java.util.regex): no Python-only syntax.
_CRED = (r"\botp\b|o\.t\.p|one.?time.?password|ओटीपी|ఓటీపీ|ఒటిపి|ಒಟಿಪಿ|ಓಟಿಪಿ|ஓடிபி|ഒടിപി|ওটিপি|ઓટીપી|ਓਟੀਪੀ|"
         r"upi\s*pin|\bm-?pin\b|atm\s*pin|\bpin\b(?!\s*code)|\bcvv\b|password|passcode|verification code|security code|"
         r"reversal code|\bthe code\b|पिन(?!\s*कोड)|पासवर्ड|పిన్(?!\s*కోడ్)|పాస్‌?వర్డ్|ಪಿನ್(?!\s*ಕೋಡ್)|ಪಾಸ್‌?ವರ್ಡ್|"
         r"பின் (நம்பர்|எண்)|பின்னை|கடவுச்சொல்")
_ASK = (r"\b(share|tell|give|read|send|forward|enter|type|provide|bata\w*|bhej\w*|de do|dijiye|daal\w*)\b|"
        r"बता|बोल(ो|िए|ें|ना)|भेज|दीजिए|दे दो|डाल|शेयर कर|चेप्पंडि|चेप्पु|"
        r"చెప్పండి|చెప్పు|చెప్పాలి|పంపండి|ఇవ్వండి|ఎంటర్|షేర్ చేయండి|"
        r"ಹೇಳಿ|ಕಳುಹಿಸಿ|ಹಂಚಿಕೊಳ್ಳಿ|ನಮೂದಿಸಿ|சொல்லுங்கள்|சொல்லவும்|அனுப்புங்கள்|பகிருங்கள்|உள்ளிடவும்")
_W = r"[^.!?।\n]{0,40}?"   # "nearby, in the same sentence"

_RULES = [
    # --- impersonation and threats
    (r"digital\s*arrest|डिजिटल\s*अरेस्ट|డిజిటల్\s*అరెస్ట్|ಡಿಜಿಟಲ್\s*ಅರೆಸ್ಟ್|டிஜிட்டல்\s*அரெஸ்ட்", 3,
     "Mentions 'digital arrest' (does not exist in law)", "digital_arrest"),
    (r"\b(cbi|ncb|enforcement directorate|ed officer|crime branch|cyber cell)\b|सीबीआई|क्राइम ब्रांच|సీబీఐ|ಸಿಬಿಐ|சிபிஐ", 2,
     "Claims to be a central agency / police unit", "agency"),
    (r"arrest\s*warrant|\bwarrant\b|will be arrested|arrest (you|kar)|गिरफ्तार|गिरफ़्तार|वारंट|అరెస్ట్|ಬಂಧನ|ಬಂಧಿಸ|கைது", 2,
     "Threat of arrest", "arrest_threat"),
    (r"money\s*laundering|मनी\s*लॉन्ड्रिंग|మనీ\s*లాండరింగ్|ಮನಿ\s*ಲಾಂಡರಿಂಗ್|\bhawala\b|हवाला|హవాలా", 3,
     "Accuses you of money laundering", "laundering"),
    (r"police case|\bfir\b\s*(registered|filed|lodged|darj|दर्ज)|एफआईआर|पुलिस (केस|कंप्लेंट)|मामला दर्ज|case (registered|filed) against you|"
     r"పోలీస్ కేసు|ಪೊಲೀಸ್ ಕೇಸ್|போலீஸ் (வழக்கு|கேஸ்)", 2, "Threatens a police case", "police_case"),
    (r"call(ing)? from (the |your |a )?bank|bank (se|nunchi|ninda) (call|phone)|bank (wale|walon|vaalu)|"
     r"बैंक से (कॉल|फोन)|బ్యాంక్ నుండి (కాల్|ఫోన్|మాట్లాడ)|ಬ್ಯಾಂಕ್‌?ನಿಂದ (ಕರೆ|ಫೋನ್)", 2, "Someone claiming to be your bank", "bank_claim"),
    (r"\bkyc\b" + _W + r"(expir|pending|update|incomplete|suspend|block)|(update|verify|complete) (your |the )?(kyc|pan|aadhaar)|"
     r"केवाईसी|కేవైసీ|ಕೆವೈಸಿ", 2, "KYC / PAN update demand", "kyc"),
    (r"\b(account|a/c|card|yono|wallet)\b" + _W + r"(will be|is being|has been|get|gets)\s*(blocked|suspended|frozen|deactivated|closed)|"
     r"block ho jayega|band ho jayega|अकाउंट (ब्लॉक|बंद|सस्पेंड)|खाता (ब्लॉक|बंद)|బ్లాక్ అవుతుంది|ಬ್ಲಾಕ್ ಆಗ|முடக்கப்படும்", 2,
     "Threatens to block your account", "block_threat"),
    (r"\btrai\b|\b(sim|mobile number|connection)\b" + _W + r"(blocked|block|deactivat\w*|disconnect\w*|band)|सिम (बंद|ब्लॉक)|"
     r"సిమ్ బ్లాక్|నంబర్ బ్లాక్", 2, "Threatens to block your SIM / number (TRAI story)", "sim_block"),
    (r"press (one|nine|1|9)\b|\b(1|9) (dabaye|दबाएं|दबाइए)|(9|1) నొక్కండి|(1|9) ಒತ್ತಿ|(1|9) அழுத்தவும்", 2,
     "Automated call asking you to press a key", "press_key"),
    (r"\b(parcel|courier|fedex|dhl|consignment)\b|पार्सल|కొరియర్|పార్సెల్|ಪಾರ್ಸೆಲ್|ಕೊರಿಯರ್|பார்சல்", 2, "Parcel / courier story", "parcel"),
    (r"\b(drugs|narcotics?|mdma|contraband|illegal items)\b|ड्रग्स|नशीले|నార్కోటిక్|డ్రగ్స్|అక్రమ వస్తువులు|ಡ್ರಗ್ಸ್|போதைப்பொருள்", 2,
     "Claims drugs / illegal items were found", "drugs"),
    (r"custom(s)? duty|customs (department|officer|clearance)|gift parcel|कस्टम्स|कस्टम ड्यूटी|ಕಸ್ಟಮ್ಸ್|కస్టమ్స్|ಗಿಫ್ಟ್|గిఫ్ట్", 2,
     "Gift parcel / customs duty", "customs"),
    (r"\baadhaa?r\b|आधार|ఆధార్|ಆಧಾರ್|ஆதார்", 1, "Mentions Aadhaar", "aadhaar"),
    (r"video\s*call|वीडियो\s*कॉल|వీడియో\s*కాల్|ವೀಡಿಯೊ\s*ಕರೆ|வீடியோ\s*கால்|\bskype\b", 2, "Moves you to a video call", "video_call"),
    (r"pay (a |the )?(fine|penalty)|\bpenalty\b|fine of (rs|₹|\d)|जुर्माना|జరిమానా|ದಂಡ|அபராதம்", 2, "Demands a fine or penalty", "fine"),
    (r"electricity (power|connection|office|officer|department)|\bbijli\b|बिजली|కరెంట్|విద్యుత్|ವಿದ್ಯುತ್|மின்சார|மின் (இணைப்பு|கட்டண)|"
     r"power (will be )?(cut|disconnected)|meter update|मीटर अपडेट|कनेक्शन (कट|काट)|connection (will be )?(cut|disconnected)", 2,
     "Electricity disconnection story", "electricity"),
    # --- pressure
    (r"right now|immediately|urgent(ly)?|within (\d+|one|two|24) (minutes?|hours?|hrs?)|\btonight\b|aaj raat|\bturant\b|तुरंत|फ़ौरन|फौरन|"
     r"వెంటనే|वेंटने|ತಕ್ಷಣ|உடனடியாக|உடனே", 2, "Creates urgency", "urgency"),
    (r"(don'?t|do not|never) (tell|inform) (anyone|anybody|your family|family|others|bank|police)|keep (this|it) (a )?secret|"
     r"kisi (aur )?ko (bhi )?(mat|na) bata|किसी (और )?को (भी )?(मत|ना|न) बता|एवरिकी चेप्पोद्दु|ఎవరికీ చెప్పొద్దు|ఎవరికీ చెప్పకండి|ಯಾರಿಗೂ ಹೇಳಬೇಡ|யாரிடமும் சொல்ல (வேண்டாம்|கூடாது)", 3,
     "Demands secrecy", "secrecy"),
    (r"\bwarna\b|वरना|otherwise we|or else|ఇల్లేకపోతే|లేకపోతే|ಇಲ್ಲದಿದ್ದರೆ|இல்லையென்றால்", 2, "Threat: do this or else", "or_else"),
    (r"new number|naya number|नया नंबर|kotha number|కొత్త నంబర్|phone (fell|broke|is broken|got stolen)|mic is not working|"
     r"(please )?don'?t call( me)?\b|call mat karna", 2, "'New number' / don't call me back", "new_number"),
    (r"accident|एक्सीडेंट|ఆక్సిడెంట్|ಅಪಘಾತ|விபத்து|\bairport\b|ఎయిర్‌పోర్ట్|immigration|ఇమ్మిగ్రేషన్|\bjail\b|జైలు|जेल", 2,
     "Relative in trouble / emergency story", "emergency"),
    # --- harmful asks
    (r"(" + _ASK + r")" + _W + r"(" + _CRED + r")|(" + _CRED + r")" + _W + r"(" + _ASK + r")", 3,
     "Asks you to share an OTP / PIN / password / code", "cred_ask"),
    (r"(" + _CRED + r")", 1, "Mentions an OTP / PIN / password", "cred_mention"),
    (r"(enter|type|daal\w*|डाल|ನಮೂದಿಸಿ|ఎంటర్)" + _W + r"(pin|पिन|పిన్|ಪಿನ್)|(pin|पिन|పిన్|ಪಿನ್)" + _W + r"(enter|daal\w*|डाल|ನಮೂದಿಸಿ|ఎంటర్)|"
     r"scan" + _W + r"(to )?(receive|get) (the )?(money|payment|amount|cashback)", 3,
     "Asks you to enter your UPI PIN / scan to RECEIVE money", "upi_receive"),
    (r"scan (the |this )?qr|qr code|collect request|approve (the |this )?request|क्यूआर|स्कैन|अप्रूव|रिक्वेस्ट|స్కాన్|క్యూఆర్|రిక్వెస్ట్|ಕ್ಯೂಆರ್|ಸ್ಕ್ಯಾನ್|ரிக்வெஸ்ட்", 2,
     "QR / UPI collect request", "qr"),
    (r"anydesk|any\s*desk|teamviewer|team viewer|quick\s*support|rustdesk|airdroid|screen\s*shar(e|ing)|स्क्रीन शेयर|స్క్రీన్ షేర్", 3,
     "Asks to install a screen-sharing / remote-access app", "remote"),
    (r"safe\s*account|सेफ\s*अकाउंट|सुरक्षित खाते|verification\s*account|rbi (safe |verification )?account|आरबीआई के? (सेफ )?(खाते|अकाउंट)|"
     r"సేఫ్ అకౌంట్|ಸೇಫ್ ಅಕೌಂಟ್", 3, "Asks you to move money to a 'safe' / verification account", "safe_account"),
    (r"(please|kindly|pls|immediately|urgently|must|need to|have to|asked (me )?to|told (me )?to|you to|then|just|now|and)\s+(\w+\s+){0,2}?"
     r"(send|transfer|pay|deposit|prepay)\b" + _W + r"(money|amount|rs\b|inr|₹|\d|lakh|thousand|account|upi)|"
     r"(^|[.!?\n:]\s*)(send|transfer|deposit)\b" + _W + r"(money|amount|rs\b|₹|\d|lakh)|"
     r"पैसे (भेज|ट्रांसफर|जमा)|(रुपये|रुपए|पैसे)" + _W + r"(भेज|ट्रांसफर|जमा) (करें|कीजिए|करो|कर दो|दीजिए)|ट्रांसफर (करें|कीजिए|करो|कर दो)|"
     r"paise (bhejo|bhej do|transfer karo)|\d[\d,]*\s*(rs|rupees?|rupaye)?" + _W + r"\b(bhejo|bhej do|transfer karo|repay karo)\b|"
     r"(रुपये|रुपए|पैसे|लाख)" + _W + r"(देने होंगे|देना होगा|भरने होंगे|जमा करने होंगे|दे दीजिए)|"
     r"(ರೂಪಾಯಿ|ಹಣ)" + _W + r"ಕಳುಹಿಸಿ|(రూపాయలు|డబ్బు)" + _W + r"(పంపండి|కట్టండి)|"
     r"డబ్బు(లు)? పంపండి|ట్రాన్స్‌?ఫర్ చేయండి|పంపించండి|ಹಣ ಕಳುಹಿಸಿ|ವರ್ಗಾವಣೆ ಮಾಡಿ|பணம் அனுப்புங்கள்|பணத்தை அனுப்ப", 3,
     "Asks you to send / transfer money", "money_ask"),
    (r"processing fee|registration fee|insurance fee|clearance fee|redelivery fee|gst pehle|fee (pehle|first|before)|"
     r"pay (a |the )?(small |processing |registration |delivery |customs |clearance )?(fee|charges)\b|फीस (पहले|जमा)|शुल्क (जमा|भर)|"
     r"జీఎస్టీ .{0,30}కట్టాలి|ఫీజు .{0,20}(కట్టాలి|కట్టండి)|ముందుగా కట్టాలి|ಶುಲ್ಕ .{0,20}(ಪಾವತಿಸಿ|ಕಟ್ಟಿ)|கட்டணம் .{0,20}(செலுத்த|கட்ட)", 3,
     "Asks for a fee before paying you (advance fee)", "fee_ask"),
    (r"(tax|fee|charges?|deposit|pay)" + _W + r"(withdraw|withdrawal|unlock|release)|(withdraw|withdrawal|निकाल|विड्रॉल)" + _W +
     r"(tax|fee|charge|टैक्स|फीस|शुल्क|pay|deposit|जमा)|विड्रॉल|విత్‌?డ్రా", 3, "Must pay to withdraw your own money", "withdraw_fee"),
    (r"(install|download)\b" + _W + r"\b(app|apk|application)\b|\.apk\b|ऐप (डाउनलोड|इंस्टॉल)|डाउनलोड करके|download karke|"
     r"యాప్ (డౌన్‌?లోడ్|ఇన్‌?స్టాల్)", 2, "Asks you to install an app", "install"),
    (r"(click|tap|open|visit|update|verify|login|log in)\b" + _W + r"(link|here|below|https?://|www\.|bit\.ly)|link (par|pe) click|लिंक पर क्लिक|"
     r"లింక్ (క్లిక్|ఓపెన్)|ಲಿಂಕ್ ಕ್ಲಿಕ್|லிங்க் கிளிக்", 2, "Asks you to click a link / log in", "click_ask"),
    (r"https?://|www\.|bit\.ly|tinyurl", 1, "Contains a link", "link"),
    (r"bit\.ly|tinyurl|is\.gd|cutt\.ly|http://|\.(top|xyz|click|online|site|live|icu|buzz|help|info)\b|\b[a-z0-9]+-(kyc|update|verify|refund|redelivery|login|secure)\b", 2,
     "Suspicious-looking link (shortener / odd domain)", "bad_link"),
    (r"(call|contact|whatsapp|message|sampark)\b" + _W + r"(\+91[\s-]?)?\b[6-9][0-9X]{4}\s?[0-9X]{5}\b|संपर्क" + _W + r"\b[6-9][0-9X]{9}\b", 2,
     "Asks you to call a personal mobile number", "call_number"),
    (r"(\bto|\bon|\bin) this (account|number|upi)|\bis (number|upi|account) (pe|par)|इस (नंबर|अकाउंट|यूपीआई) पर|ఈ నంబర్‌కి|ఈ అకౌంట్|ಈ ಯುಪಿಐ", 2,
     "Send money to a given number / account", "given_account"),
    # --- lures
    (r"lottery|lucky draw|you (have )?won|\bprize\b|\bjeete\b|जीते|इनाम|लॉटरी|लकी ड्रॉ|\bkbc\b|గెలిచారు|లాటరీ|లక్కీ డ్రా|బహుమతి|ಗೆದ್ದಿದ್ದೀರಿ|ಲಾಟರಿ|வென்ற|பரிசு|லாட்டரி", 2,
     "Says you won a prize / lucky draw", "prize"),
    (r"guarantee[d]? (return|profit|income)|double (your )?money|\d+\s*%\s*(daily|monthly|weekly|return|profit|per month|per day)|ipo allotment", 3,
     "Guaranteed / unrealistic returns", "returns"),
    (r"\bdouble\b|दोगुना|రెట్టింపు|ದ್ವಿಗುಣ|இரட்டிப்பு|guarantee|गारंटी|గ్యారంటీ|ಖಾತರಿ|உத்தரவாதம்", 2, "Promises guaranteed or doubled money", "returns"),
    (r"whatsapp group|telegram|टेलीग्राम|டெலிகிராம்|టెలిగ్రామ్|trading app|stock tips?|vip group|\bcrypto|கிரிப்டோ", 1, "Investment group / app", "invest_channel"),
    (r"like kar|daily \d{3,}|daily rs|रोज़? \d{3,}|ghar baithe|घर बैठे|kamaye|kamao|कमाएं|कमाओ|earn (rs|₹|\d|upto|up to|daily)|"
     r"part[-\s]?time job|work from home|like and earn|review and earn|సంపాదించ|ಸಂಪಾದಿಸ|சம்பாதி", 2, "Easy-money job offer", "easy_money"),
    (r"\btasks?\b|\breviews?\b|రివ్యూ|రేటింగ్|ರಿವ್ಯೂ|\bratings?\b|google maps|గూగుల్ మ్యాప్స్", 1, "Paid tasks / reviews", "task"),
    (r"\brefund\b|cashback|रिफंड|కాష్‌?బ్యాక్|ಕ್ಯಾಶ್‌?ಬ್ಯಾಕ್", 1, "Refund / cashback offer", "refund"),
    (r"loan app|instant loan|cashnow|pre-?approved (instant |personal )?loan|no cibil|without cibil|लोन ऐप|इंस्टेंट लोन|ఇన్‌?స్టంట్ లోన్|లోన్ యాప్|கடன் செயலி", 2,
     "Loan offer / loan app", "loan"),
    (r"morphed|\bmorph\b|contacts ko|contacts (and|aur) family|सारे कॉन्टैक्ट|(send|bhej\w*|share)" + _W + r"(all )?(your )?contacts|కాంటాక్ట్స్|ಕಾಂಟ್ಯಾಕ್ಟ್", 3,
     "Threatens to message your contacts / morphed photos", "contacts_threat"),
    (r"video viral|viral kar|obscene|\bnude|अश्लील|न्यूड|screen recording|आत्महत्या", 3, "Threatens to leak an intimate video", "intimate_leak"),
]
_COMPILED = [(re.compile(p, re.I), w, label, fam) for p, w, label, fam in _RULES]

# Rules about OTPs/PINs run on text where protective clauses are blanked out, so "Do not share this OTP",
# "Bank never asks for your PIN" or a victim saying "I will not share my OTP" don't count as a request.
_MASKED_FAMILIES = {"cred_ask", "cred_mention", "upi_receive"}
_ASK_FAMILIES = {"cred_ask", "upi_receive", "remote", "safe_account", "money_ask", "fee_ask", "withdraw_fee",
                 "click_ask", "install", "call_number", "given_account", "press_key", "secrecy"}
_CLAUSE_SRC = r"[^.!?।॥\n,;]+"
_NEG_SRC = (r"\b(not|never|don'?t|dont|won'?t|wont|cannot|can'?t|nobody|no one|nahi|nahin|mat|kabhi)\b|n't\b|"
            r"नहीं|मत|कभी|न करें|ना करें|వద్దు|ద్దు|ఎప్పుడూ|வேண்டாம்|மாட்டோம்|ஒருபோதும்|கேட்காது|ಬೇಡ|ಎಂದಿಗೂ|ಕೇಳುವುದಿಲ್ಲ")
_VERB_SRC = (r"share|disclose|reveal|tell|give|ask|request|call|शेयर|साझा|बता|मांग|माँग|पूछ|\bदें\b|bata|maang|"
             r"షేర్|చెప్ప|అడగ|అడుగ|ఇవ్వ|பகிர|சொல்ல|கேட்க|ಹಂಚ|ಹೇಳ|ಕೇಳ")
# "...don't tell anyone, just tell ME the OTP" must still count: never blank a clause that points the code at the sender.
_GUARD_SRC = r"\b(me|mujhe|humein)\b|मुझे|हमें|నాకు|మాకు|எனக்கு|ನನಗೆ"
_SENTENCE_SRC = r"[^.!?।॥\n]+"
_SENTENCE, _CLAUSE, _NEG, _VERB, _GUARD = (re.compile(s, re.I) for s in (_SENTENCE_SRC, _CLAUSE_SRC, _NEG_SRC, _VERB_SRC, _GUARD_SRC))
_CRED_RX = re.compile(_CRED, re.I)

# Looks like a bank / wallet transaction alert or OTP notice (not a request).
_TXN_SRC = (r"\b(debited|credited|avl\.? ?bal|available balance|a/c (no\.? )?x+\d+|ac x+\d+|card ending|txn|ref no|upi ref|"
            r"valid for \d+ ?min)|डेबिट|क्रेडिट|जमा किए गए|डेबिट किए गए")
_TXN = re.compile(_TXN_SRC, re.I)

_QUESTION_SRC = r"^(do|does|is|are|can|will|should|what|how|why|kya|क्या|ఏ|ಏನು)\b.*\?\s*$"
_QUESTION = re.compile(_QUESTION_SRC, re.I | re.S)

# Legacy keys kept in the export so older app builds can still load new rules.
_LEGACY_PROTECTIVE = r"(never|not|n't)\s+(ask|share|call)|do not share|don'?t share|never share"
_LEGACY_ASKS_OTP = r"(share|tell|give|read|bata|batao)\W+(\w+\W+){0,3}(otp|pin)"


def mask_protective(text: str) -> str:
    """Blank out clauses that WARN about sharing credentials ('do not share this OTP')."""
    def clause(m):
        c = m.group(0)
        if _NEG.search(c) and _VERB.search(c) and _CRED_RX.search(c):
            return " " * len(c)
        return c

    def sentence(m):
        sent = m.group(0)
        return sent if _GUARD.search(sent) else _CLAUSE.sub(clause, sent)
    return _SENTENCE.sub(sentence, text)


def scan(text: str, segments: list[dict] | None = None) -> dict:
    """Return matched red flags and a risk floor (0-80) the LLM's score can't go below."""
    masked = mask_protective(text)
    best: dict[str, dict] = {}          # family -> strongest hit
    for rx, weight, label, fam in _COMPILED:
        m = rx.search(masked if fam in _MASKED_FAMILIES else text)
        if m and (fam not in best or weight > best[fam]["weight"]):
            best[fam] = {"label": label, "match": m.group(0).strip(), "weight": weight, "family": fam}
    if "cred_ask" in best:
        best.pop("cred_mention", None)   # the ask already covers the mention
    hits = list(best.values())

    # Emotional pressure from batch STT: fear/anger/urgency in the call's segments.
    emotions = [str(s.get("emotion") or "").lower() for s in (segments or [])]
    pressure = sum(e in ("fear", "anger", "angry", "fearful", "anxious", "urgent") for e in emotions)
    if pressure >= 2:
        hits.append({"label": f"Emotional pressure detected in {pressure} segments", "match": "", "weight": 1, "family": "emotion"})

    score = sum(h["weight"] for h in hits)
    strong = sum(h["weight"] == 3 for h in hits)
    families = {h["family"] for h in hits}
    asks = families & _ASK_FAMILIES
    floor = 0
    if strong >= 2:
        floor = 80
    elif strong >= 1 and score >= 10:
        floor = 80
    elif strong >= 1 and score >= 5:
        floor = 60
    elif score >= 8 and asks and len(families) >= 4:
        floor = 60
    elif score >= 4 and len(families) >= 2:
        floor = 35
    # A bank/OTP notification with no request in it is not a scam just because it says OTP, debit or account.
    transactional = bool(_TXN.search(text)) and not asks
    if transactional:
        floor = 0
    # A short general question ("Do police arrest people on video calls?") is not itself a scam.
    if len(text) < 200 and _QUESTION.match(text.strip()) and strong == 0:
        floor = 0
    return {"hits": hits, "score": score, "risk_floor": floor, "transactional": transactional}


def export_rules() -> dict:
    """Everything the phone app needs to run the same keyword scan on-device."""
    return {
        "version": 2,
        "rules": [{"pattern": p, "weight": w, "label": label, "family": fam, "masked": fam in _MASKED_FAMILIES}
                  for p, w, label, fam in _RULES],
        "mask": {"sentence": _SENTENCE_SRC, "clause": _CLAUSE_SRC, "negation": _NEG_SRC, "verbs": _VERB_SRC, "credential": _CRED, "guard": _GUARD_SRC},
        "ask_families": sorted(_ASK_FAMILIES),
        "transaction": _TXN_SRC,
        "question": _QUESTION_SRC,
        "floors": {"strong2": 80, "strong1_and_score10": 80, "strong1_and_score5": 60, "score8_ask_four_families": 60, "score4_two_families": 35},
        # legacy (v1 app builds)
        "protective": _LEGACY_PROTECTIVE,
        "protected_labels": sorted(label for p, w, label, fam in _RULES if fam in _MASKED_FAMILIES),
        "asks_otp": _LEGACY_ASKS_OTP,
    }


def knowledge_block() -> str:
    pb = "\n".join(f"- {name}: {desc}" for name, desc in PLAYBOOKS.items())
    facts = "\n".join(f"- {f}" for f in OFFICIAL_FACTS)
    return f"KNOWN SCAM PLAYBOOKS (India):\n{pb}\n\nVERIFIED FACTS YOU MAY CITE:\n{facts}"
