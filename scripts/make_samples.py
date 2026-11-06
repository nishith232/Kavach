"""Generate demo scam-call recordings with Gnani Timbre (two voices = caller + victim).

Run from the project root:  python -m scripts.make_samples
Creates samples/*.wav. Upload them in the app to test long-audio (batch) transcription
with speaker separation. These are synthetic, clearly fictional calls for testing only.
"""
import asyncio
import io
import wave
from pathlib import Path

from app import config, gnani

OUT = Path("samples")
CALLER, VICTIM = "Avinash", "Lakshmi"   # timbre-v3.0 voices (each speaks all 10 languages)
RATE = 16000

SCRIPTS = {
    "hindi_digital_arrest": ("hi-IN", [
        (CALLER, "नमस्ते, मैं मुंबई साइबर क्राइम से इंस्पेक्टर राजेश बोल रहा हूँ। आपके आधार कार्ड से एक पार्सल बुक हुआ है जिसमें ड्रग्स मिले हैं।"),
        (VICTIM, "क्या? मैंने तो कोई पार्सल नहीं भेजा।"),
        (CALLER, "आपके नाम पर मनी लॉन्ड्रिंग का केस है और गिरफ्तारी का वारंट निकला है। अभी आपको डिजिटल अरेस्ट किया जा रहा है। वीडियो कॉल पर रहिए और किसी को मत बताइए।"),
        (VICTIM, "मैं क्या करूँ? मुझे बहुत डर लग रहा है।"),
        (CALLER, "वेरिफिकेशन के लिए अपने खाते के सारे पैसे आरबीआई के सेफ अकाउंट में तुरंत ट्रांसफर कीजिए। जाँच के बाद पैसे वापस मिल जाएँगे।"),
    ]),
    "telugu_kyc_otp": ("te-IN", [
        (CALLER, "హలో, నేను మీ బ్యాంక్ నుండి మాట్లాడుతున్నాను. మీ కేవైసీ అప్‌డేట్ కాలేదు, ఈరోజు రాత్రికి మీ అకౌంట్ బ్లాక్ అవుతుంది."),
        (VICTIM, "అయ్యో, ఇప్పుడు ఏం చేయాలి?"),
        (CALLER, "కంగారు పడకండి. మీ ఫోన్‌కి ఒక ఓటీపీ వచ్చింది, అది వెంటనే నాకు చెప్పండి. ఈ విషయం ఎవరికీ చెప్పొద్దు."),
        (VICTIM, "సరే, ఒక్క నిమిషం చూస్తాను."),
    ]),
    "english_investment": ("en-IN", [
        (CALLER, "Hi, this is Priya from Alpha Wealth. You were added to our WhatsApp group for premium stock tips."),
        (VICTIM, "Okay, what is this about?"),
        (CALLER, "We guarantee thirty percent monthly returns with IPO allotment. Just install our trading app from this link and deposit fifty thousand today, the offer closes in one hour."),
        (VICTIM, "Thirty percent every month? That sounds very high."),
    ]),
    "telugu_safe_delivery": ("te-IN", [
        (CALLER, "హలో సార్, నేను డెలివరీ బాయ్‌ని. మీ ఆర్డర్ వచ్చింది, మీ ఇంటి గేట్ దగ్గర ఉన్నాను."),
        (VICTIM, "సరే, రెండు నిమిషాల్లో వస్తాను. పేమెంట్ ఆల్రెడీ ఆన్‌లైన్‌లో చేశాను."),
        (CALLER, "అవును సార్, ప్రీపెయిడ్ ఆర్డర్. ఏమీ కట్టనవసరం లేదు. థాంక్యూ."),
    ]),
}

SMS = """# Sample messages to paste into Kavach (fictional, for testing)

1) SCAM - electricity
Dear Consumer, your electricity power will be disconnected tonight at 9.30 pm because your previous month bill was not updated. Please immediately contact our electricity officer 98XXXXXX10. Thank you.

2) SCAM - task job (Hinglish)
Hello! Part time job available. Daily 3000-8000 rs kamaye sirf YouTube videos like karke. Abhi join karo Telegram pe, pehle task ka 150 rs turant milega.

3) SAFE - real OTP SMS
123456 is your OTP for login to your bank account. Valid for 5 minutes. Do not share this OTP with anyone. Bank never asks for OTP.

4) SCAM - courier (Telugu)
మీ FedEx పార్సెల్‌లో అక్రమ వస్తువులు ఉన్నాయి. వెంటనే 9 నొక్కండి, లేకపోతే మీపై పోలీస్ కేసు నమోదు అవుతుంది.

5) Follow-up question to try after a scam verdict
I already told them the OTP and 20,000 rupees got debited. What should I do now?
"""


def silence(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"\x00\x00" * int(RATE * seconds))
    return buf.getvalue()


async def make(name: str, lang: str, lines):
    clips = []
    for voice, text in lines:
        clips.append(await gnani.synthesize(text, lang, voice=voice, sample_rate=RATE))
        clips.append(silence(0.6))
    path = OUT / f"{name}.wav"
    path.write_bytes(gnani.join_wavs(clips))
    print(f"  {path}  ({gnani.wav_seconds(path.read_bytes()):.0f}s)")


async def main():
    assert config.GNANI_API_KEY, "Set GNANI_API_KEY in .env first"
    OUT.mkdir(exist_ok=True)
    (OUT / "sample_messages.txt").write_text(SMS, encoding="utf-8")
    print("Generating demo calls with Gnani Timbre:")
    for name, (lang, lines) in SCRIPTS.items():
        await make(name, lang, lines)
    print("  samples/sample_messages.txt")


if __name__ == "__main__":
    asyncio.run(main())
